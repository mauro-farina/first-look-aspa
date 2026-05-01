from typing import List, Dict, Set

# ASPA verification outcomes
ASPA_NO_ATTESTATION = 'No Attestation'
ASPA_PROVIDER = 'Provider+'
ASPA_NOT_PROVIDER = 'Not Provider+'


class ASPAVerifier:
    """
    ASPA AS Path Verification procedures as defined in the 
    Internet-Draft: https://datatracker.ietf.org/doc/html/draft-ietf-sidrops-aspa-verification
    """

    
    def __init__(self, aspa: Dict[str, Set[str]]):
        """
        Initialize the ASPAVerifier with an ASPA dictionary.
        
        Args:
            aspa: Dictionary where keys are customer ASNs (as strings) and values are 
                  sets/lists of authorized provider ASNs (as strings).
        """
        self.aspa = aspa
    
    def authorized(self, as_customer: str, as_provider: str) -> str:
        """
        Check if an AS is authorized as a provider for a customer AS.
        
        Args:
            as_customer: The customer AS number (as string).
            as_provider: The provider AS number (as string).
            
        Returns:
            ASPA_NO_ATTESTATION: If the customer AS has no ASPA record.
            ASPA_PROVIDER: If the provider is authorized.
            ASPA_NOT_PROVIDER: If the provider is not authorized.
        """
        if str(as_customer) not in self.aspa:
            return ASPA_NO_ATTESTATION
        if str(as_provider) in self.aspa[str(as_customer)]:
            return ASPA_PROVIDER
        else:
            return ASPA_NOT_PROVIDER
    
    @staticmethod
    def get_compressed_path(path: List[str]) -> List[str]:
        """
        Remove consecutive duplicate ASNs from a path (path compression).
        
        Args:
            path: List of ASNs representing the AS path.
            
        Returns:
            Compressed path with consecutive duplicates removed.
        """
        if not path:
            return []
        
        compressed_path = [path[0]]
        for asn in path[1:]:
            if asn != compressed_path[-1]:
                compressed_path.append(asn)
        
        return compressed_path
    
    def max_up_ramp(self, path: List[str]) -> int:
        """
        Determine the maximum up-ramp length.
        
        Assumed path has already been compressed and is ordered having path[-1] as the 
        originating AS, and path[0] as the neighboring AS.
        
        Determine the maximum up-ramp length as I, where I is the minimum index for which 
        authorized(A(I), A(I+1)) returns "Not Provider+".
        If there is no such I, the maximum up-ramp length is set equal to the 
        COMPRESSED_AS_PATH length N.
        
        Args:
            path: Compressed AS path.
            
        Returns:
            Maximum up-ramp length.
        """
        n = len(path)

        # i is the minimum index for which authorized(A(I), A(I+1)) returns "Not Provider+"
        # min index, but path goes from path[0] (neighboring AS) to path[-1] (originating AS)
        for i in range(1, n):
            a = self.authorized(path[-i], path[-i - 1])
            if a == ASPA_NOT_PROVIDER:
                return i
        
        return n  # If there is no such I, the maximum up-ramp length is set equal to N
    
    def min_up_ramp(self, path: List[str]) -> int:
        """
        Determine the minimum up-ramp length.
        
        Assumed path has already been compressed and is ordered having path[-1] as the 
        originating AS, and path[0] as the neighboring AS.
        
        The minimum up-ramp length can be determined as I, where I is the minimum index 
        for which authorized(A(I), A(I+1)) returns "No Attestation" or "Not Provider+".
        If there is no such I, the COMPRESSED_AS_PATH consists of only "Provider+" pairs; 
        so the minimum up-ramp length is set equal to the COMPRESSED_AS_PATH length N.
        
        Args:
            path: Compressed AS path.
            
        Returns:
            Minimum up-ramp length.
        """
        n = len(path)
        for i in range(1, n):
            a = self.authorized(path[-i], path[-i - 1])
            if a == ASPA_NOT_PROVIDER or a == ASPA_NO_ATTESTATION:
                return i
        
        return n  # If there is no such I, the minimum up-ramp length is set equal to N
    
    def max_down_ramp(self, path: List[str]) -> int:
        """
        Determine the maximum down-ramp length.
        
        Assumed path has already been compressed and is ordered having path[-1] as the 
        originating AS, and path[0] as the neighboring AS.
        
        The maximum down-ramp length can be determined as N - J + 1 where J is the maximum 
        index for which authorized(A(J), A(J-1)) returns "Not Provider+".
        If there is no such J, the maximum down-ramp length is set equal to the 
        COMPRESSED_AS_PATH length N.
        
        Args:
            path: Compressed AS path.
            
        Returns:
            Maximum down-ramp length.
        """
        n = len(path)

        for i in range(0, n - 1):
            a = self.authorized(path[i], path[i + 1])
            if a == ASPA_NOT_PROVIDER:
                j = n - i
                return n - j + 1
        
        return n  # If there is no such J, the maximum down-ramp length is set equal to N
    
    def min_down_ramp(self, path: List[str]) -> int:
        """
        Determine the minimum down-ramp length.
        
        Assumed path has already been compressed and is ordered having path[-1] as the 
        originating AS, and path[0] as the neighboring AS.
        
        The minimum down-ramp length can be determined as N - J + 1 where J is the maximum 
        index for which authorized(A(J), A(J-1)) returns "No Attestation" or "Not Provider+".
        If there is no such J, the minimum down-ramp length is set equal to the 
        COMPRESSED_AS_PATH length N.
        
        Args:
            path: Compressed AS path.
            
        Returns:
            Minimum down-ramp length.
        """
        n = len(path)

        for i in range(0, n - 1):
            a = self.authorized(path[i], path[i + 1])
            if a == ASPA_NOT_PROVIDER or a == ASPA_NO_ATTESTATION:
                j = n - i
                return n - j + 1
        
        return n  # If there is no such J, the minimum down-ramp length is set equal to N
    
    def verify_upstream_path(self, path: List[str]) -> str:
        """
        Verify an AS path received from a Customer or Peer.
        
        path is assumed to be a list where path[-1] is the AS originating the announcement, 
        path[0] is the neighboring AS sending the path.
        
        Args:
            path: Compressed AS path to verify.
            
        Returns:
            'Invalid', 'Unknown', or 'Valid'.
        """
        # 1. If the AS_PATH is empty, then the procedure halts with the outcome "Invalid".
        if len(path) == 0:
            return 'Invalid'

        path = self.get_compressed_path(path)
        n = len(path)

      
        # 4. If max_up_ramp < N, the procedure halts with the outcome "Invalid".
        if self.max_up_ramp(path) < n:
            return 'Invalid'
        
        # 5. If min_up_ramp < N, the procedure halts with the outcome "Unknown".
        if self.min_up_ramp(path) < n:
            return 'Unknown'

        # 6. Else, the procedure halts with the outcome "Valid".
        return 'Valid'
    
    def verify_downstream_path(self, path: List[str]) -> str:
        """
        Verify an AS path received from a Provider.
        
        path is assumed to be a list where path[-1] is the AS originating the announcement.
        
        Args:
            path: Compressed AS path to verify.
            
        Returns:
            'Invalid', 'Unknown', or 'Valid'.
        """
        # 1. If the AS_PATH is empty, then the procedure halts with the outcome "Invalid".
        if len(path) == 0:
            return 'Invalid'
        
        path = self.get_compressed_path(path)
        n = len(path)
        
        # 4. If max_up_ramp + max_down_ramp < N, the procedure halts with the outcome "Invalid".
        if self.max_up_ramp(path) + self.max_down_ramp(path) < n:
            return 'Invalid'
        
        # 5. If min_up_ramp + min_down_ramp < N, the procedure halts with the outcome "Unknown".
        if self.min_up_ramp(path) + self.min_down_ramp(path) < n:
            return 'Unknown'
        
        # 6. Else, the procedure halts with the outcome "Valid".
        return 'Valid'
    

def run_tests():
    """
    Test cases to verify implementation correctness.
    https://github.com/ksriram25/IETF/blob/main/ASPA_path_verification_examples.pdf
    """
    
    test_aspa = {
        # Simple cases
        'A': {'C', 'D'},
        'B': {'E'},
        'C': {'F'},
        'D': {'F', 'G'},
        'G': {'AS0'},
        # E and F have no ASPA records
        # ---
        # Comples cases
        'H': {'AS0'},  # Tier-1
        'K': {'AS0'},  # Tier-1
        'L': {'K'},
        'P': {'AS0'},  # Tier-1
        'Q': {'AS0'},  # Tier-1
        'R': {'Q'},
        'S': {'R'},
        # J has no ASPA
    }
    
    verifier = ASPAVerifier(test_aspa)
    
    test_results = []
    
    def run_test(test_name, path, verification_type, expected_result):
        if verification_type == 'upstream':
            result = verifier.verify_upstream_path(path)
        else:
            result = verifier.verify_downstream_path(path)
        
        passed = result == expected_result
        test_results.append({
            'name': test_name,
            'path': path,
            'type': verification_type,
            'expected': expected_result,
            'got': result,
            'passed': passed
        })
    
    # Upstream Path Verification (Table 1)
    
    run_test(
        "Table 1, #1",
        ['F', 'C', 'A'],
        'upstream',
        'Valid'
    )
    
    run_test(
        "Table 1, #2",
        ['D', 'C', 'A'],
        'upstream',
        'Invalid'
    )
    
    run_test(
        "Table 1, #3",
        ['D', 'F', 'C', 'A'],
        'upstream',
        'Unknown'
    )
    
    run_test(
        "Table 1, #4",
        ['D', 'E', 'B'],
        'upstream',
        'Unknown'
    )
    
    run_test(
        "Table 1, #5",
        ['A', 'D', 'E', 'B'],
        'upstream',
        'Invalid'
    )
    
    run_test(
        "Table 1, #6",
        ['A', 'D', 'G', 'E', 'B'],
        'upstream',
        'Invalid'
    )
    
    run_test(
        "Table 1, #7",
        ['A', 'C', 'F'],
        'upstream',
        'Invalid'
    )
    
    run_test(
        "Table 1, #8",
        ['A', 'C', 'F', 'G'],
        'upstream',
        'Invalid'
    )
    
    run_test(
        "Table 1, #9",
        ['E', 'B'],
        'upstream',
        'Valid'
    )
    
    # Downstream Path Verification (Table 2)
    
    run_test(
        "Table 2, #1",
        ['E', 'G', 'F', 'C', 'A'],
        'downstream',
        'Unknown'
    )
    
    run_test(
        "Table 2, #2",
        ['E', 'G', 'D', 'A'],
        'downstream',
        'Valid'
    )

    run_test(
        "Table 2, #3",
        ['E', 'D', 'C', 'A'],
        'downstream',
        'Unknown'
    )
    
    run_test(
        "Table 2, #4",
        ['E', 'G', 'D', 'C', 'A'],
        'downstream',
        'Invalid'
    )
    
    run_test(
        "Table 2, #5",
        ['C', 'F', 'D', 'G'],
        'downstream',
        'Unknown'
    )
    
    run_test(
        "Table 2, #6",
        ['D', 'G', 'E', 'B'],
        'downstream',
        'Valid'
    )
    
    run_test(
        "Table 2, #7",
        ['C', 'D', 'G', 'E', 'B'],
        'downstream',
        'Invalid'
    )
    
    run_test(
        "Table 2, #8",
        ['F', 'C', 'A'],
        'downstream',
        'Valid'
    )
    
    run_test(
        "Table 2, #9",
        ['E', 'A'],
        'downstream',
        'Valid'
    )
    
    run_test(
        "Table 2, #10",
        ['E', 'C', 'A'],
        'downstream',
        'Valid'
    )
    
    # Complex BGP Relationships (Table 3)
    
    run_test(
        "Table 3, #1",
        ['J', 'H'],
        'upstream',
        'Invalid'
    )
    
    run_test(
        "Table 3, #2",
        ['J', 'H'],        
        'upstream',
        'Invalid'
    )
    
    run_test(
        "Table 3, #3",
        ['K', 'J', 'H'],
        'downstream',
        'Invalid'
    )

    run_test(
        "Table 3, #4",
        ['Q', 'P'],
        'upstream',
        'Invalid'
    )
    
    run_test(
        "Table 3, #5",
        ['Q', 'P'],
        'downstream',
        'Valid'
    )

    run_test(
        "Table 3, #6",
        ['R', 'Q', 'P'],
        'downstream',
        'Valid'
    )
    
   
    passed = 0

    for test in test_results:

        if test['passed']:
            passed += 1
            continue

        print(f"Test: {test['name']}")
        print(f"\tPath: {test['path']}")
        print(f"\tType: {test['type']}")
        print(f"\tExpected: {test['expected']}, Got: {test['got']}")
        print()
    
    print(f"{passed}/{len(test_results)} tests passed")


if __name__ == "__main__":
    run_tests()
